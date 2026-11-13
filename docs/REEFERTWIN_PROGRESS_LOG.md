# REEFERTWIN AI Progress Log

## 2026-11-13

### CFG-001 — Configuration isolation

- **Plan:** Add an explicit configuration-loading boundary so tests do not
  inherit repository `.env` values.
- **Implementation:** Added `load_environment` to `src/config.py`; tests use
  `load_environment=False` and provide required environment values explicitly.
- **Verification:** `pytest -q` passed with **30 passed**; Python compileall
  passed; offline health check returned status `ok`.
- **Result:** Completed and recorded in the task tracker.

### SQL persistence baseline

- **Inspection:** `src/twin/state_manager.py` currently stores events and
  vehicle projections in in-memory dictionaries only.
- **Inspection:** `src/database.py` provides SQL Server connection-string and
  query validation helpers, but no Twin persistence repository.
- **Inspection:** migrations `001_create_twin_schema.sql` and
  `002_extend_phase2_audit.sql` exist; live application against SQL Server was
  not run.
- **Status:** SQL connectivity, ODBC Driver 18, migration application,
  persistent projections, scenario isolation, audit retrieval, restart
  persistence, and least-privilege behavior remain unverified. These tasks are
  pending or blocked in the tracker; no mock result is represented as live
  persistence.

### SQL-001 / SQL-002 — Connectivity and migration boundary

- **Driver check:** `pyodbc` reported Microsoft ODBC Driver 18 for SQL Server
  as installed.
- **Connectivity check:** `python scripts\check_startup.py --check-sql`
  timed out connecting to `127.0.0.1:1433`.
- **Environment inspection:** No SQL Server or SQL Browser Windows service,
  `sqlservr` process, or registered SQL Server instance was found. Docker
  Desktop's Linux engine is unavailable. TCP 1433 and 1434 are closed; MySQL
  3306 and PostgreSQL 5432 are listening.
- **Configured endpoint:** The application `.env` selects host `127.0.0.1`,
  port `1433`, and database `master`. No password or token values are recorded
  here.
- **Implementation:** Added
  `scripts/migrations/003_persistent_scenarios_actions_audit.sql` for
  scenario, action, and Twin audit tables without modifying legacy tables.
- **Migration review:** Migration 001 depends on the pre-existing
  `FDE_VIEWS` schema and `USR_FDE_RO`; migration 002 assumes
  `FDE_VIEWS.AgentAuditLog` exists; migration 003 depends on migrations 001
  and 002 plus the same read principal. This execution did not apply or
  alter any migration.
- **Implementation:** Extended `src/twin/sql_store.py` with parameterized event,
  telemetry, baseline projection, scenario, and audit persistence paths. A
  scenario event never updates `Twin.Vehicles`.
- **Verification:** Focused unit tests passed (`9 passed`) using a fake engine
  to verify generated statements and transaction boundaries. Live migration
  and persistence remain blocked by SQL availability.
- **Regression:** Full `pytest -q` passed with **34 passed**; compileall passed.
- **Disposition:** SQL-001 is blocked by the missing SQL Server service/endpoint.
  No service, firewall, Docker, credential, or migration changes were made.

### SQL-007 — SQL endpoint provenance and setup recommendation

- **Repository configuration:** `.env` uses `SQL_SERVER_HOST`,
  `SQL_SERVER_PORT`, and `SQL_DATABASE`; the current non-secret endpoint is
  `127.0.0.1:1433` with database `master`.
- **Ingestion path:** `scripts/ingest_legacy_data.py` uses the configured
  SQLAlchemy connection and loads the legacy table; it does not define a
  remote or Azure endpoint.
- **Deployment path:** `docker-compose.yml` defines a local SQL Server
  Developer container and points the application at the Compose service name
  `sqlserver`. The deployment workflow connects to EC2 over SSH but does not
  configure a separate database host.
- **Documentation path:** the runbooks describe SQL Server Developer Edition in
  Docker, using `localhost:1433` for local development and an EC2-hosted
  container for deployment. They do not provide an existing remote SQL or
  Azure SQL hostname.
- **Finding:** `127.0.0.1:1433` is an intended local/container endpoint, not
  evidence of an existing remote database. The intended legacy database could
  be reused only if an approved SQL Server container or EC2 instance exists
  and its persistent volume/schema are verified first.
- **Recommendation:** Native SQL Server Developer Edition installation on
  Windows is not necessary. The safest setup is to reuse an approved existing
  Docker/EC2 SQL Server; if none exists, obtain approval to start the
  documented Docker SQL Server container with a secret supplied through the
  environment. No installation, credential, or migration action was taken.

### SIM-001 — What-if simulation state consistency

- **Reproduction:** Creating a failed-compressor scenario for REEFER-003
  produced critical compressor risk with unchanged instantaneous temperature.
  Advancing 15 minutes changed baseline REEFER-003 from 2.9339°C to 3.0512°C
  while the scenario remained at 2.9339°C. The What-if page also passed its
  independent vehicle selector into comparison.
- **Root causes:** Scenario projections were snapshots with no clock-sync path;
  `ScenarioProjection` had no enforced vehicle identity; and warehouse ranking
  treated a missing deadline as feasible. Initial single-observation compressor
  risk is correctly critical, but has no defensible threshold-crossing estimate.
- **Implementation:** Scenario projections retain `vehicle_id`, reject
  mismatched comparisons/recommendations/additions, and synchronize failed
  compressor temperatures with the existing `project_temperature` model after
  baseline ticks. The UI preserves the selected scenario and displays its
  associated vehicle; reset clears scenario/action selections. Unknown
  deadline feasibility is explicitly rejected.
- **Tests:** Added association, wrong-vehicle rejection, scenario progression,
  baseline isolation, reset/replay, and unknown deadline assertions in
  `tests/unit/test_phase4_scenarios.py`.
- **Verification:** Focused scenario tests `10 passed`; full `pytest -q`
  `39 passed`;
  compileall passed. After 15 minutes the scenario reached 3.0689°C with a
  107.5-minute estimated breach while baseline remained 3.0512°C.
- **Limitation:** The vehicle selector remains for choosing a new scenario;
  selected scenario comparison and ranking always derive from its associated
  vehicle. Non-compressor disruptions remain snapshots until domain-specific
  progression rules are defined.

### UI-MANUAL-001 — Embedded Streamlit user manual

- **Implementation:** Added a `User Manual` sidebar page that loads
  `docs/USER_MANUAL.md` as UTF-8 markdown through
  `render_user_manual()`. Missing or unreadable documentation is shown as an
  explicit Streamlit error.
- **Verification:** Added a dashboard regression test for the manual asset;
  focused dashboard tests and full test execution passed, and Python
  compilation passed.

### CLOUD-001 — Streamlit Community Cloud startup hardening

- **Reproduction:** A temporary project root without `.env` previously raised
  `ConfigurationError`. Source tracing also found agent SQL configuration and
  LangGraph/LLM construction at import time.
- **Implementation:** `load_config` now treats `.env` as optional and applies
  environment > Streamlit secrets > `.env` precedence. It supports explicit
  `REEFERTWIN_MODE` and `REEFERTWIN_AI_ENABLED` values. Agent tools load
  configuration only when invoked, and the orchestrator builds the graph only
  when the AI page is used. Missing services return typed or degraded states
  instead of blocking deterministic pages.
- **Demo mode:** `REEFERTWIN_MODE=demo` keeps deterministic dashboard pages
  available, disables AI by default, and avoids claims of SQL persistence.
- **Security:** Streamlit XSRF protection remains enabled and CORS is set to a
  compatible secure value. Error messages no longer include raw agent or audit
  exception details.
- **Documentation:** Added
  `docs/STREAMLIT_CLOUD_DEPLOYMENT.md` and the placeholder-only
  `.streamlit/secrets.toml.example`.
- **Verification:** No-env configuration probe passed; lazy module imports
  passed; demo UI import succeeded; configuration/optional-service tests
  passed (`12 passed`); full suite passed (`47 passed`); compileall passed.
- **Limitation:** Actual Streamlit Community Cloud deployment was not
  performed, so hosted-provider connectivity and cloud build execution remain
  unverified.
