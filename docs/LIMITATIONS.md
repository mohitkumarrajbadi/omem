# What OMem does not do

Plain limits for architects and compliance reviewers.

## Positioning

- OMem is the audit, governance, and state-rollback layer. It is not a
  hit-rate competitor to Mem0, Zep, or a vector database.
- Local `add` / `remember` stores what you wrote. It does not run an LLM
  extractor. Latency ratios against extract-on-write systems are not
  comparisons of the same operation.
- Diligence retrieval suites under `distribution/` (LongMemEval, LoCoMo,
  STATE-Bench, KV probes) are optional lab artifacts. They are not the
  product claim and are not quoted on the README.

## Governance boundaries

- Application-level namespace isolation tests are not a Postgres row-level
  security proof. Live RLS for `omem_app` is operator evidence in omem-cloud
  (`make rls-proof`).
- Setting `OMEM_ENCRYPTION_KEY` enables AES-256-GCM at rest. Without that key,
  content is not field-encrypted.
- Right-to-erasure workflows depend on retention / deletion policy
  configuration and on operators actually running them. Exporting the audit
  trail does not by itself delete source systems outside OMem.

## Reliability

- Crash-resume smoke tests are not a failure rate. The chaos suite reports a
  rate (`scripts/chaos_resume.py`, nightly CI). Treat unpublished rates as
  unproven.

## Cloud is not GA

OMem Cloud is a design-partner preview. It does not currently provide:

- multi-region high availability
- a load-test SLO gate on every commit
- key rotation as a product flow (operator procedure only)

See [`omem-cloud/PRODUCTION_READINESS.md`](../../omem-cloud/PRODUCTION_READINESS.md).

## Observability and Alpha surfaces

- HTTP OpenTelemetry in omem-os is not full auto-instrumentation. omem-cloud
  instruments some routes, not every route.
- The Python AST codebase index and the local dashboard are Alpha. They are
  not part of the enterprise audit pitch.
