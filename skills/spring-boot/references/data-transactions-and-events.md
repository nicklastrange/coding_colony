# Data, Transactions, and Events

## Contents

- Transaction boundaries and proxies
- Persistence and query design
- Migrations and concurrency
- Events and async work
- Review examples
- Official references

## Transaction boundaries and proxies

- Place a transaction around one complete application-service unit of work. Keep protocol mapping in controllers and storage mechanics in repositories.
- Annotate a concrete Spring-managed method or class. Confirm that the call enters from another bean through the proxy; self-invocation does not start a new proxied transaction in the default mode.
- For per-item independent commits, cross a real proxy boundary through a separate collaborator or use an explicit transaction template. Do not use self-injection or `AopContext` to make internal calls transactional.
- Remember the default rollback rule: unchecked exceptions and `Error` roll back; checked exceptions do not unless configured. Test the actual exception path when rollback is part of correctness.
- Treat `readOnly = true` as a routing or optimization hint, not a write prohibition or security control.
- Change propagation and isolation only for a demonstrated concurrency or composition requirement. Document the anomaly or nested behavior being prevented and test it against the production database engine.
- Avoid remote calls, user interaction, and slow non-database work inside an open database transaction. They hold connections and locks while an unrelated system controls latency.
- Do not assume a thread-bound imperative transaction follows work into `@Async`, a new thread, or an arbitrary coroutine dispatcher.
- Use a reactive transaction manager only with a reactive return type and one Reactor-context pipeline. Do not block inside it or combine it with imperative thread-local assumptions.
- Avoid transactional work from constructors or `@PostConstruct`; proxy advice is not available there.
- Catch only product-classified rejection failures outside the transactional call when a batch may continue. Let infrastructure and programming failures escape instead of reporting them as invalid input.

```java
@Service
class OrderService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    @Transactional
    OrderId place(PlaceOrder command) {
        Order order = orders.save(Order.from(command));
        events.publishEvent(new OrderPlaced(order.id()));
        return order.id();
    }
}
```

## Persistence and query design

- Keep persistence entities behind the persistence/application boundary. Do not serialize them directly from controllers or bind requests into them.
- Understand entity state before calling `save`: Spring Data JPA chooses persist or merge through new-state detection. Manually assigned identifiers can require an explicit `Persistable.isNew()` strategy.
- Rely on dirty checking only within a clear persistence context. Do not assume detached mutation will be written or that an extra `save` repairs unclear ownership.
- Design the fetch plan for each use case. Use a projection, fetch join, or entity graph when the read contract needs related data; do not make every association eager to hide a lazy-loading failure.
- Detect N+1 behavior with an integration test, SQL statistics, or trace rather than intuition. Assert query count only when the repository has stable support for it.
- Keep lazy access inside a deliberate transaction or map to a read model there. Do not rely accidentally on Open Session in View.
- Paginate or stream large results and require a deterministic order. An unbounded `findAll` or unstable page sort is a production risk.
- Treat derived query names as executable contracts. Use an explicit query when the name becomes ambiguous, excessively long, or unable to express the required fetch and locking behavior.
- Flush in tests when database constraints, generated values, or SQL execution timing matter; a passing in-memory object assertion does not prove the database accepted the write.
- Use the production database engine when dialect behavior, JSON or array types, native queries, migrations, collation, locks, or constraints are part of the change.
- Test propagation through the real proxy. For `REQUIRES_NEW`, prove the inner commit survives a deliberate outer rollback and query again from a fresh transaction.

## Migrations and concurrency

- Make every schema change through the repository's migration tool. Keep entities and migrations in the same change and validate startup against both an empty schema and a representative upgraded schema when risk warrants it.
- Prefer expand-and-contract migrations for rolling deployments: add compatible structure, deploy dual-compatible code, migrate data, then remove old structure later.
- Make data migrations bounded, restartable, and observable. Avoid locking an entire large table in an application-startup migration without an operational plan.
- Enforce invariants at the database boundary when concurrent writers could bypass an application-only check. Translate constraint failures into the established domain/API error.
- Add `@Version` for optimistic locking when lost updates must be detected. Test the competing-update failure and retry or user-visible behavior.
- Use pessimistic locks only with a proven contention model, deterministic lock order, timeout behavior, and deadlock handling.

## Events and async work

- Remember that ordinary Spring application events are synchronous in the publisher's thread by default. A listener failure can fail the publisher.
- Use `@TransactionalEventListener` when execution depends on commit or rollback phase. By default it does not run without a transaction unless fallback execution is explicitly enabled.
- Treat `AFTER_COMMIT` work as outside the committed unit. Its failure cannot roll back the transaction that already committed.
- Do not write through resources left over from the completed transaction and assume another commit will occur. Start an explicit new transaction for local post-commit writes or hand durable work to an appropriate delivery mechanism.
- Use an in-process event only when process loss and lack of cross-instance delivery are acceptable. Use a durable outbox or broker only when the requirements demand durable external delivery.
- Make listeners idempotent when retries, duplicate delivery, or replay are possible.
- Treat `@Async` as proxy-based. Self-invocation is synchronous, and `void` failures do not reach the caller.
- Give async work a named, bounded executor, observable queue behavior, timeout or cancellation policy, and explicit error handling.
- Do not use `@Async` as a bean lifecycle callback or assume transaction, security, logging, or tracing thread-local state propagates automatically.

```java
@Component
class OrderProjectionUpdater {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPlaced event) {
        // Keep local follow-up retry-safe; use durable delivery when loss is forbidden.
    }
}
```

## Review examples

Reject self-invoked transaction assumptions:

```java
void importAll(List<Row> rows) {
    for (Row row : rows) {
        importOne(row); // Does not enter the proxy on this instance.
    }
}

@Transactional(propagation = REQUIRES_NEW)
void importOne(Row row) { /* ... */ }
```

Reject eager loading as an N+1 patch; instead define the use-case query and verify its SQL behavior.

## Official references

- [Declarative transaction annotations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Transaction implementation and context](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Data JPA transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Data JPA entity persistence](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html)
- [Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Async annotation support](https://docs.spring.io/spring-framework/reference/integration/scheduling.html#scheduling-annotation-support-async)
