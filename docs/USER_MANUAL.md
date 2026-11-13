# REEFERTWIN AI Digital Twin

## 1. Prerequisites

- Windows PowerShell
- Python 3.12
- SQL Server is optional for the local twin dashboard, but required for live
  telemetry, audit logs, and database-backed agent tools.
- An LLM configuration supported by the project (`OLLAMA`, `OPENAI`, or
  `DEEPSEEK`) is required for the AI Command Centre.

## 2. Install

From the project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

## 3. Configure environment

Create `D:\ENGINEER\NLDS\cold-chain-logistics\.env`. Never commit this file.

```dotenv
SQL_SERVER_HOST=localhost
SQL_SERVER_PORT=1433
SQL_DATABASE=master
SQL_AGENT_USER=USR_FDE_RO
SQL_AGENT_PASSWORD=<agent-password>
SQL_CONNECT_TIMEOUT_SECONDS=10
Agent_llm=OLLAMA
```

For administrator audit access, also add:

```dotenv
SQL_ADMIN_USER=sa
SQL_ADMIN_PASSWORD=<admin-password>
```

For cloud LLMs, set `Agent_llm=OPENAI` or `Agent_llm=DEEPSEEK` and provide
the corresponding API key expected by the configured environment.

## 4. Validate configuration

```powershell
python scripts\check_startup.py
```

To also verify SQL connectivity:

```powershell
python scripts\check_startup.py --check-sql
```

## 5. Optional SQL Server setup

Start a local SQL Server container if one is not already available:

```powershell
docker run -e "ACCEPT_EULA=Y" `
  -e "MSSQL_SA_PASSWORD=<strong-password>" `
  -p 1433:1433 `
  --name legacy-mssql `
  -d mcr.microsoft.com/mssql/server:2022-latest
```

Apply the migrations in order with an administrator connection:

```powershell
sqlcmd -S localhost,1433 -d master -U sa -P "<admin-password>" `
  -i scripts\migrations\001_create_twin_schema.sql

sqlcmd -S localhost,1433 -d master -U sa -P "<admin-password>" `
  -i scripts\migrations\002_extend_phase2_audit.sql
```

Seed the deterministic demo fleet:

```powershell
python scripts\seed_twin.py
```

## 6. Start the application

```powershell
streamlit run src\ui.py
```

Open the URL printed by Streamlit, normally
`http://localhost:8501`.

## 7. Use the command centre

The sidebar contains these pages:

- **Overview**: fleet metrics, alerts, route map, and current health.
- **Digital Twin**: select a vehicle to inspect telemetry, shipment details,
  temperature history, risk state, and evidence.
- **Fleet**: filter vehicles by `normal`, `warning`, `critical`, or `unknown`.
- **Simulation Lab**: explicitly advance the deterministic scenario by 1, 5,
  or 15 minutes, or reset it to the same baseline.
- **What-if Lab**: create isolated compressor, heatwave, temperature, traffic,
  closure, capacity, and warehouse scenarios; compare baseline versus
  disruption; rank feasible cold-storage destinations; and approve/execute a
  simulated diversion.
- **AI Command Centre**: ask the LangGraph assistant for operational analysis.
- **Audit**: authenticate with administrator credentials and inspect audit
  records.

Refreshing the browser or changing pages does not advance the simulation.
Only the **Advance simulation** button mutates the session-local demo state.

## 8. Run tests

```powershell
python -m unittest discover -s tests\unit -p "test_*.py" -v
```

The current unit suite covers configuration, telemetry simulation, predictive
risk, workflow controls, Phase 3 dashboard state, Phase 4 scenarios, and Phase
5 health checks.

## 9. Common limitations

- The local dashboard uses deterministic in-memory demo state unless SQL
  persistence is explicitly wired and available.
- Weather, Pinecone, SQL, and cloud LLM integrations require valid services
  and credentials.
- Risk estimates indicate temperature-threshold timing; they are not
  spoilage or shelf-life predictions.

## 10. Phase 5 deployment checks

Run the machine-readable offline health check:

```powershell
python scripts\health_check.py
```

For a live SQL readiness check:

```powershell
python scripts\health_check.py --check-sql
```

Run the container locally:

```powershell
docker compose up --build
```

The container exposes Streamlit on port `8501`, restarts automatically, and
has a health check. The GitHub Actions workflow runs compilation, unit tests,
offline health validation, and a container build on pushes to `main`.
Deployment is manual through **Actions → REEFERTWIN CI and Deploy →
Run workflow**. The target host must provide the configured secrets, Python
environment, SQL access, and the `streamlit` systemd service. The workflow
reinstalls dependencies, runs startup/tests, restarts the service, and checks
Streamlit's health endpoint before succeeding.
