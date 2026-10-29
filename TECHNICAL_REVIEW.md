# Technical Review & Architecture Report

## 1. Top 3 Production Risks Identified & Mitigated

### Risk 1: Double-Spend / Balance Underflow via Concurrent Withdrawals
- **Root Cause:** The original `/withdraw` endpoint implemented a naive read-modify-write pattern without database locks or transaction isolation. Two simultaneous withdrawal requests for $80 on a $100 balance would both read $100, pass validation, and commit, draining $160 from the wallet.
- **Mitigation:**
  - Implemented pessimistic row-level locking via `SELECT ... FOR UPDATE` (`with_for_update()`), ensuring atomic serialization of all balance modifications per wallet.
  - Added a database-level `CheckConstraint('balance >= 0')` to physically prevent negative balances at the engine layer.
  - Added idempotency key verification (`reference`) scoped per user, returning HTTP 200 on exact re-delivery and HTTP 409 Conflict if parameters are tampered with.

### Risk 2: Arbitrary Credit Injection via Unvalidated Deposits
- **Root Cause:** `/deposits/verify` trusted user-supplied amounts, failed to check the receiving wallet address (`to`), accepted transactions regardless of blockchain status or token type, ignored block confirmation depth, and lacked deduplication. An attacker could claim 1,000,000 USDT on a 10 USDT transfer or re-claim the same hash repeatedly.
- **Mitigation:**
  - Strict on-chain verification against provider data: Ethereum network only, USDT token contract, recipient address matching `0xmerchant`, and status strictly `success`.
  - Enforced a minimum confirmation threshold of $\ge 12$ blocks.
  - Enforced exact numerical matching between on-chain transferred amount and requested amount.
  - Implemented global deduplication on `(reference, kind='deposit')` to prevent replay attacks across retries and across different users.
  - Handled external provider RPC downtime gracefully with HTTP 503 instead of crashing with 500.

### Risk 3: Multi-Tenant Data Leakage & IDOR (Detail & AI Endpoints)
- **Root Cause:**
  - `GET /transactions/{id}` lacked an ownership check, allowing any unauthenticated caller to access another user's financial records by iterating IDs.
  - `POST /ai/ask` accepted a client-controlled `user_id` in the request body, bypassing header authentication and leaking complete transaction histories (including sensitive reference keys) to an external LLM provider.
- **Mitigation:**
  - Enforced strict user scoping on `GET /transactions/{id}` (`where(Transaction.id == id, Transaction.user_id == user_id)`), returning 404 on mismatched records.
  - Bound `/ai/ask` strictly to the authenticated `user_id` from the dependency.
  - Sanitized the LLM context prompt by stripping sensitive identifiers and references, supplying only verified amounts and categories.
  - Structured the AI response into verified ledger facts and generative explanations.

---

## 2. Recommended Architectural Improvement
**Asynchronous Event-Driven Ingestion via Transaction Outbox & Blockchain Indexer**
- **Current State:** Synchronous HTTP polling of blockchain RPC nodes during user request processing binds web worker threads to slow third-party networks and exposes the system to reorg vulnerabilities.
- **Proposed Architecture:**
  - Transition deposit handling to an asynchronous worker service (e.g., using Celery or Temporal with Redis/PostgreSQL).
  - Deploy a dedicated chain watcher service that subscribes to on-chain Transfer events for `0xmerchant`.
  - Incoming deposits are recorded as `pending_confirmation`. Once the chain reaches finalized block depth ($\ge 12$ or finalized beacon block), an atomic transactional outbox publishes a credit event to the ledger service.
  - Frontend receives immediate feedback via WebSocket/Server-Sent Events (SSE) instead of synchronous user-initiated polling.

---

## 3. Junior Code Review Feedback
> *"Hi! Great work getting the initial prototype endpoints running. Before we ship this to staging, there are two critical financial programming practices we need to adopt:*
> 1. ***Never use floating-point types for currency:*** In Python and Postgres, `float` uses IEEE-754 binary representation, where numbers like `0.1 + 0.2` yield `0.30000000000000004`. In financial ledgers, this causes rounding leaks and audit failures. Always use `Decimal` with fixed precision (e.g. `Numeric(18, 2)` in DB and Python's `decimal.Decimal`).
> 2. ***Understand the Read-Modify-Write anti-pattern:*** Checking a balance in Python and saving it back with `w.balance = w.balance - amount` is safe *only* for single-threaded toy scripts. In a web server handling concurrent requests, Postgres `READ COMMITTED` isolation allows multiple transactions to read the same old state. Always lock the row with `with_for_update()` or use an atomic conditional `UPDATE` at the database level.*"

---

## 4. Production Readiness Checklist
Before releasing to production, the following infrastructure must be implemented:
1. **API Gateway Trust Boundary:** Ensure the edge reverse proxy (NGINX/Kong/Envoy) strips incoming `X-User-Id` headers from external clients and injects it only after validating a cryptographic JWT or session token.
2. **Database Connection Pool Tuning:** Monitor PgBouncer and SQLAlchemy pool size (`pool_size`, `max_overflow`, `pool_timeout`) to prevent lock starvation under heavy row contention.
3. **Structured Audit Logging & Metrics:** Emit Prometheus metrics for wallet lock wait times, deposit verification failures, and LLM cache hit/miss ratios.
4. **Rate Limiting:** Implement per-user and per-IP token bucket rate limiting on `/withdraw`, `/deposits/verify`, and `/ai/ask` to mitigate brute-force and DoS attempts.

---

## 5. Rejected Alternative
**Alternative: Postgres `SERIALIZABLE` Isolation Level instead of Row-Level Locks**
- **Why Rejected:** While `SERIALIZABLE` isolation guarantees strict serial execution without manual `SELECT FOR UPDATE` locks, Postgres implements this via optimistic software checks (SIREAD locks). Under high concurrency (e.g., flash-sale withdrawals or automated trading bots), concurrent conflicting transactions fail with `40001 serialization_failure`, forcing complex client-side retry logic and thrashing the database engine.
- **Decision:** Explicit row locking (`SELECT FOR UPDATE`) on the specific wallet row deterministically queues contending transactions in Postgres, resulting in predictable throughput without transaction abort storms.