# Web, Testing, and Operations

## Contents

- HTTP and validation
- Error and security contracts
- Test selection
- Runtime and startup proof
- Review examples
- Official references

## HTTP and validation

- Keep request and response DTOs distinct from persistence entities and internal commands when their contracts differ.
- Apply bean validation to request shape and method parameters at the boundary. Enforce cross-record, stateful, and authorization invariants in the application layer.
- Account for both object-binding and method-validation failure paths in the global error contract; different controller signatures can raise different Spring validation exceptions.
- Use centralized advice and the repository's established `ProblemDetail` or error-envelope convention. Keep status, machine code, field or parameter errors, and client-safe detail stable.
- Do not return raw exception messages. Map expected failures explicitly and let unexpected failures become one sanitized internal-error response with server-side diagnostics.
- Preserve content negotiation, media types, character encoding, pagination metadata, and backward compatibility when changing a controller signature.
- Keep one web model. In MVC, avoid blocking the request thread unnecessarily; in WebFlux, never call blocking persistence or clients on the event loop.
- Configure CORS through Spring Security or MVC integration so preflight is handled in the intended order. Do not add permissive wildcard origins with credentials.

```java
@RestControllerAdvice
final class ApiErrors {
    @ExceptionHandler(OrderNotFound.class)
    ProblemDetail notFound(OrderNotFound ignored) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, "The requested order does not exist");
        problem.setProperty("code", "order_not_found");
        return problem;
    }
}
```

## Error and security contracts

- Start authorization from deny by default. Make public routes explicit and keep actuator, documentation, and error endpoints within the intended policy.
- Authenticate at the request boundary and enforce ownership, tenant, or domain permissions at the operation that has enough context to decide.
- Enable method security explicitly when annotations are part of the design; adding the security starter alone does not activate it.
- Keep the real security filter chain in web tests. Cover anonymous, insufficient-authority, valid-authority, ownership, CSRF where applicable, and CORS preflight behavior.
- Never disable CSRF globally merely to make a browser-facing mutation test pass. Choose the correct session, token, or stateless API model.
- Treat redirects, login entry points, access denied, validation failure, and domain failure as separate observable contracts.
- Avoid high-cardinality or sensitive values in logs, metrics, traces, and error bodies.

## Test selection

- Use a plain unit test for domain logic and a service whose collaborators can be constructed directly. Do not start Spring for code that does not need the container.
- Use one focused slice for one boundary. Use an MVC or WebFlux slice for routing, serialization, validation, advice, filters, and security; use a data slice for mappings, queries, constraints, and flush behavior.
- Do not combine several slice annotations. Import only the required supporting configuration and supply direct collaborators with the mocking facility supported by the project's Spring version.
- Use `@SpringBootTest` for cross-layer wiring, conditional configuration, full property binding, security configuration, startup runners, transaction composition, and event integration.
- Know that the default `@SpringBootTest` web environment starts no real server. Use a random-port environment when embedded-server startup and the actual HTTP stack are under test.
- Use the application's main method in a startup test when it customizes `SpringApplication` and the project's Boot version supports that option.
- Use Testcontainers and the production engine when dialects, migrations, constraints, locks, native queries, or container-wired services matter. Prefer Boot service connections when supported by the installed version.
- Remember that many transactional data tests roll back automatically. Force flush or commit and clean data explicitly when commit-time behavior is the subject.
- Remember that a random-port server runs work in a different thread from the test client; a transaction on the test method does not roll back server-side writes.
- Test failure and recovery signals, not only the happy response: invalid configuration, unavailable dependency behavior, duplicate write, timeout, authorization, rollback, and retry where their risks exist.

## Runtime and startup proof

- Derive commands from the checked-in wrapper and existing CI or run documentation. Do not assume a global Gradle or Maven installation.
- Use a safe profile and non-production credentials. Supply representative real dependencies or controlled containers for every required startup connection.
- For context-only wiring risk, run the smallest full-context test that loads the relevant configuration and fails on missing or ambiguous beans and invalid properties.
- For server, filter, route, packaging, or main-method risk, build the executable artifact, start it as deployed, wait for readiness or health, exercise one meaningful endpoint, and stop it cleanly.
- Distinguish liveness from readiness. Use the application's own signal when available; a listening TCP port alone can precede migration, runner, or dependency readiness.
- Capture the exact command, active profiles, infrastructure, exit status, decisive log or health signal, exercised request, and shutdown result.
- Treat a startup that requires an uncontrolled production service as unsafe, not as permission to skip proof. Use the repository's test profile, container setup, or a focused context test and report any remaining operational gap.
- Re-run startup after dependency, migration, environment, packaging, plugin, or generated-resource changes even if compilation and unit tests pass.

## Review examples

Select proof by risk:

```text
Pure price calculation       -> plain unit test
Controller validation        -> focused web slice with real advice/filter chain
JPA query or constraint      -> data slice against production database engine
Conditional bean/property    -> full context with representative properties
Server/filter/packaging      -> random-port or packaged-application startup + request
```

Reject `contextLoads()` as the only evidence when the change affects real server startup, migrations, filters, routes, or packaging.

## Official references

- [Spring MVC validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Safe web data binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring MVC REST exceptions and `ProblemDetail`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Security authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/)
- [Spring Boot testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Testing Spring Boot applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot test slices](https://docs.spring.io/spring-boot/appendix/test-auto-configuration/slices.html)
- [Spring Boot Testcontainers support](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
