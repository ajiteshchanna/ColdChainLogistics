# REEFERTWIN AI Task Tracker

This tracker is the execution checklist for the implementation plan. A task is
completed only when its acceptance criteria and verification method have
passed. Database, credential, and deployment actions require explicit approval
before execution.

| ID | Priority | Task | Dependencies | Acceptance criteria | Verification | Status |
|---|---|---|---|---|---|---|
| CFG-001 | P0 | Isolate configuration loading in tests | None | Tests can clear environment without inheriting repository `.env` values | `pytest -q`, compileall, offline health | Done |
| SQL-001 | P0 | Verify SQL Server and ODBC Driver 18 | None | Real connection succeeds with configured credentials and Driver 18 is available | `health_check.py --check-sql`, service/listener/driver inspection | Blocked: Driver 18 installed; no local SQL Server instance/service; Docker daemon unavailable; 1433/1434 closed |
| SQL-007 | P0 | Determine SQL endpoint provenance | None | Configuration and documentation identify whether SQL is local, remote, Azure-hosted, or container-hosted | Review `.env` names, ingestion, Compose, deployment, and runbooks without exposing secrets | Done: local/EC2 Docker design; no remote endpoint configured |
| SQL-002 | P0 | Version Twin schema migrations | SQL-001 | Idempotent migrations create Twin entities, indexes, views, and audit structures without changing legacy tables | Apply twice to disposable SQL Server and inspect schema | Blocked: migration reviewed; live application unavailable |
| SQL-003 | P0 | Persist telemetry and projections | SQL-002 | Events are append-only, idempotent, transactional, and update state versions | SQL integration tests with duplicate events and rollback | Pending |
| SQL-004 | P0 | Persist isolated scenarios | SQL-003 | Scenario events and projections never update baseline records | Scenario integration tests and baseline comparison | Pending |
| SQL-005 | P0 | Persist audit records | SQL-002 | Correlated append-only audit records include status, evidence, approval, and errors | Insert/retrieve integration test and UI retrieval test | Pending |
| SQL-006 | P0 | Verify restart persistence | SQL-003, SQL-005 | Telemetry, projections, scenarios, and audit survive app/database restart | Restart recovery test against real SQL Server | Blocked by SQL-001 |
| SEC-001 | P0 | Verify least-privilege access | SQL-002 | Read account can use curated views and append audit only; legacy/Twin writes are denied | Permission integration test with separate accounts | Blocked by SQL-001 |
| EXT-001 | P0 | Verify Ollama and Pinecone integrations | None | Live calls succeed or explicit degraded/unavailable envelopes are shown | Integration tests with configured services | Blocked: services/credentials unavailable |
| EXT-002 | P1 | Verify weather and routing adapters | None | Timeout, malformed response, cache, fixture, and live provenance states are explicit | Adapter tests plus live smoke test when configured | Pending |
| DEP-001 | P0 | Verify Docker and deployment workflow | None | Image builds, health checks, CI gates, deployment, and rollback are demonstrated | Docker/CI/EC2 smoke and rollback test | Blocked: Docker/EC2 unavailable |
| DEMO-001 | P0 | Verify persistent end-to-end demo | SQL-004, SQL-005, EXT-001, DEP-001 | Compressor failure flow completes with persistent state, approval, metrics, and audit | Three-minute scripted rehearsal | Pending |
| P1-001 | P1 | Complete ULIP/LDB boundary | None | Mock/live adapter has typed envelope and provenance; no live claim in mock mode | Unit and contract tests | Pending |
| P1-002 | P1 | Add geospatial visualization and analytics hardening | Phase 4 local demo | Route overlays, cost, carbon, and missing-input states are explicit | Browser smoke and formula tests | Pending |
| P2-001 | P2 | Add durable graph checkpoints and monitoring | SQL persistence | Restart-safe graph state and debounced alert workflow | Restart and monitoring integration tests | Pending |

| SIM-001 | P0 | Debug what-if state consistency | None | Scenario identity, baseline isolation, deterministic progression, risk, and warehouse feasibility are consistent across navigation and clock advancement | Focused repro, regression tests, full pytest | Done |
| SIM-001a | P0 | Trace scenario state | SIM-001 | Reproduced baseline/scenario drift, vehicle mismatch, and unknown-deadline feasibility | Runtime probe and source trace | Done |
| SIM-001b | P0 | Isolate scenario progression | SIM-001a | Scenarios retain vehicle identity, progress independently, and reset/replay deterministically | Scenario regression tests | Done |
| SIM-001c | P0 | Harden warehouse safety decisions | SIM-001a | Unknown breach deadlines are explicit and cannot be marked deadline-feasible | Warehouse regression tests | Done |
| UI-MANUAL-001 | P1 | Add Streamlit user manual | None | A User Manual navigation page displays the existing documented setup, workflows, and limitations | Focused dashboard tests and compileall | Done |
| UI-MANUAL-001a | P1 | Add manual navigation | UI-MANUAL-001 | Sidebar includes User Manual and routes to its page | Dashboard source inspection and test | Done |
| UI-MANUAL-001b | P1 | Render manual content | UI-MANUAL-001a | Existing `docs/USER_MANUAL.md` is loaded as UTF-8 markdown with explicit load errors | Dashboard asset test | Done |
| UI-MANUAL-001c | P1 | Verify manual tab | UI-MANUAL-001b | Focused tests and compilation pass; evidence is recorded | `pytest` and compileall | Done |

## Completed evidence

- `CFG-001`: `pytest -q` returned `34 passed`; `python -m compileall -q
  src scripts` passed; `python scripts\health_check.py` returned
  `{"status":"ok"}`.

- SQL persistence unit paths: focused fake-engine tests passed (`9 passed`)
  for baseline projection updates, scenario isolation, and serialized
  scenario parameters. These are not live SQL verification.

## Explicitly unresolved

- SQL Server connectivity, ODBC Driver 18 runtime availability, migrations,
  SQL projections, persistent scenarios, audit retrieval, restart recovery,
  and least-privilege execution are not verified.
- The repository does not contain a configured remote SQL Server or Azure SQL
  endpoint. Its documented deployment model is SQL Server Developer Edition in
  Docker, locally for development or on the EC2 host for deployment.
- Ollama, Pinecone, Open-Meteo, and OSRM live behavior is not verified.
- Docker build/container health, GitHub Actions execution, EC2 deployment, and
  rollback are not verified.

## SIM-001 evidence

- The repro showed baseline REEFER-003 changing from 2.9339°C to 3.0512°C
  after 15 minutes while the stored failed-compressor scenario stayed at
  2.9339°C. The What-if UI could also pass REEFER-001 to a REEFER-003
  scenario.
- A compressor scenario now advances using the existing `project_temperature`
  thermal rule while baseline telemetry and vehicle state remain untouched.
- Warehouse candidates with no safe intervention deadline are rejected with an
  explicit uncertainty reason rather than presented as deadline-safe.
- Verification: focused scenario tests `10 passed`; full `pytest -q` `39 passed`;
  `python -m compileall -q src tests scripts` passed.
