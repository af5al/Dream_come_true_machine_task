# Candidate Questionnaire (Q1 - Q22)

### Q1: Candidate Full Name
[Your Full Name]

### Q2: Position Applied For
IT Development Lead

### Q3: Primary Technology Stack Demonstrated
FastAPI (Python 3.12), SQLAlchemy 2.0, PostgreSQL 16, React 18, Vite, TypeScript, Docker Compose.

### Q4: Total Assessment Time Spent
Approximately 4 hours across environment setup, reproduction, security fixes, automated tests, frontend hardening, and technical documentation.

---

## Technical & Architecture Questions

### Q5: How did you ensure financial integrity during concurrent withdrawals?
Implemented pessimistic row-level locking via SQLAlchemy’s `with_for_update()` (`SELECT ... FOR UPDATE` on the user’s `Wallet` row) inside the transaction, serializing balance mutations. Backed this with a database check constraint (`balance >= 0`) and user-scoped idempotency keys (`reference`).

### Q6: Why is `SELECT FOR UPDATE` preferred over `SERIALIZABLE` isolation in this context?
Postgres `SERIALIZABLE` uses optimistic software predicate locks. Under concurrent withdrawal attempts on the same wallet, it aborts transactions with `40001 serialization_failure`, requiring complex application-level retries. Explicit row-locking cleanly queues contending requests at the database engine without transaction abort storms.

### Q7: Why should floating-point numbers never be used for wallet balances?
Floats use IEEE-754 binary representation, causing representation discrepancies (e.g. `0.1 + 0.2 = 0.30000000000000004`). In financial ledgers, this causes rounding leaks and bookkeeping imbalances. We migrated all currency columns to `Numeric(18, 2)` / Python `decimal.Decimal`.

### Q8: What was the vulnerability in `GET /transactions/{id}` and how was it resolved?
Insecure Direct Object Reference (IDOR). The endpoint accepted an arbitrary transaction ID without verifying caller ownership. We injected `user_id: int = Depends(current_user)` and scoped the query to `WHERE id = :id AND user_id = :user_id`, returning HTTP 404 on unowned records.

### Q9: How is the authentication trust boundary defined for `X-User-Id`?
In this assessment prototype, `X-User-Id` is received as an internal header. In production, this header is untrusted if received from clients. An API gateway or reverse proxy must terminate external TLS, validate JWT/session credentials, strip client-supplied `X-User-Id` headers, and inject the authenticated user ID into internal service requests.

### Q10: What checks were added to `/deposits/verify`?
1. External RPC exception handling returning HTTP 503 on provider downtime.
2. Network validation (`ethereum` only).
3. Token validation (`USDT` only).
4. Merchant recipient validation (`0xmerchant`).
5. Success status validation (`tx.status == 'success'`).
6. Confirmation depth enforcement ($\ge 12$ blocks).
7. Exact numerical amount matching with on-chain transfer data.
8. System-wide deduplication on `(reference, kind='deposit')` to prevent replay.

### Q11: How does the system prevent a deposit transaction hash from being credited twice?
Before crediting, the database checks for an existing completed deposit with that transaction reference. Furthermore, the credit operation and ledger insert occur atomically inside a locked wallet transaction, preventing simultaneous replay requests from crediting multiple times.

### Q12: How should blockchain reorganizations (reorgs) be handled in production?
By establishing a confirmation buffer ($\ge 12$ blocks on Ethereum or beacon chain finalization depth). For unfinalized deposits, records are stored as `pending_confirmation`. A background indexer monitors block hashes; if a reorg drops or replaces a block containing the transfer, the transaction is marked `reorg_invalidated` without touching wallet balances.

### Q13: What pagination strategy did you implement for transaction history?
Keyset (cursor) pagination ordering by `id DESC`, querying `WHERE id < :cursor LIMIT :limit + 1`. This provides $O(\log N)$ query speed, avoids $O(N)$ scanning associated with `OFFSET`, eliminates page drift/duplicates when new transactions arrive, and caps limit at 50.

### Q14: What database index supports the transaction pagination query?
A composite B-Tree index on `(user_id, id)`: `Index('ix_transactions_user_id_id', 'user_id', 'id')`.

### Q15: How were sensitive references protected on the AI assistant endpoint?
The AI context-building function was updated to exclude private payment references, transaction hashes, and foreign user records. Only sanitized, non-sensitive transaction data (`amount`, `kind`, `status`) is supplied in the prompt context.

### Q16: How does the AI endpoint handle external LLM provider downtime?
External LLM calls are isolated in a `try...except` block that returns HTTP 503 Service Unavailable with a user-friendly error message, preventing unhandled 500 server crashes.

### Q17: How is the AI cache keyed and invalidated?
Cached in-memory using a composite key `(user_id, normalized_question, latest_transaction_id)`. When a user completes a deposit or withdrawal, the `latest_transaction_id` changes, automatically invalidating the cache and ensuring subsequent AI answers reflect up-to-date account records.

### Q18: What improvements were made to the frontend application?
- Added explicit Loading, Error, and Empty data states.
- Implemented user switching (User 1, User 2, Test User 9999).
- Added transaction detail inspector view.
- Handled cursor pagination with a "Load More" action.
- Added a manual refresh trigger avoiding redundant continuous polling.

---

## Assessment Deliverable Sections

### Q19: Summary of Implemented Changes
1. **Financial Concurrency & Idempotency:** Implemented `with_for_update()` row locking, `CheckConstraint('balance >= 0')`, `Decimal` modeling, and idempotency key handling returning HTTP 200 on exact replay and HTTP 409 on parameter tampering.
2. **Crypto Deposit Verification:** Comprehensive on-chain validation (network, token, recipient, confirmation depth, exact amounts), deduplication, and RPC error handling.
3. **Multi-Tenant Access Control (IDOR):** Scoped transaction inspection and AI assistant to authenticated caller identity.
4. **Keyset Pagination:** Deterministic `id`-based cursor pagination with limit capping and composite index.
5. **AI Reliability & Privacy:** Prompt data sanitization, provider failure isolation (503), response caching, and separation of verified ledger metrics from generated text.
6. **Frontend Resilience & Testing:** Built reactive UI states and added 15 automated pytest tests running against real PostgreSQL.

### Q20: Known Limitations & Unfinished Work
1. **Synchronous Blockchain Verification:** Verification currently runs synchronously in the HTTP request cycle. In production, this should be moved to an asynchronous worker with an event-driven blockchain indexer and transactional outbox.
2. **Distributed Caching:** The AI cache is currently stored in-memory in the process (`AI_CACHE`). In a multi-worker / multi-instance deployment, this should use Redis with a TTL.
3. **Full Authentication Gateway:** Relies on the simulated `X-User-Id` header; needs real JWT/OAuth2 token validation at the edge proxy.

### Q21: AI-Assisted Development Disclosure
- **Tools Used:** Antigravity / Gemini AI pair programming assistant.
- **Scope of Assistance:** Used as an interactive senior mentor for Socratically reviewing architectural trade-offs, designing test harnesses, and reviewing edge case coverage.
- **AI Suggestion Corrected/Rejected:** During deposit validation, the assistant originally suggested wrapping the entire endpoint in a broad `try...except` returning 503. I corrected this because it masked client validation errors (`HTTP 400 Invalid Network`) as server errors (`503`). I isolated the `try...except` strictly to the external `MockChain.lookup()` RPC call.

### Q22: Supervised Live Review Readiness
Ready to demonstrate live execution of `docker compose exec backend python -m pytest`, explain architectural trade-offs, and implement live modifications without AI assistance.