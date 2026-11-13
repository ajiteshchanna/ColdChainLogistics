# Phase 0

## Ingesting data

- Download the dataset from 'data\source\data.txt'
- Create and EC2 instance > docker container > mcr.microsoft.com/mssql/server:2022-latest
- Spin up the Legacy MSSQL Server
```
docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=<strong-secret>" -p 1433:1433 --name legacy-mssql -d mcr.microsoft.com/mssql/server:2022-latest

# or multi-line in windows 
docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=<strong-secret>" ^
   -p 1433:1433 --name legacy-mssql ^
   -d mcr.microsoft.com/mssql/server:2022-latest

# or multi-line unix
docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=<strong-secret>" \
   -p 1433:1433 --name legacy-mssql \
   -d mcr.microsoft.com/mssql/server:2022-latest

# or multi-line with volume inside EC2
docker run -v mssql_data:/var/opt/mssql \
  -e "ACCEPT_EULA=Y" \
  -e "MSSQL_SA_PASSWORD=<strong-secret>" \
  -p 1433:1433 \
  --name legacy-mssql \
  -d mcr.microsoft.com/mssql/server:2022-latest

```
- install the req > pip install -r requirements.txt

Before running Python scripts, create a local `.env` file from a secret
manager or deployment environment. Do not commit it:
```
SQL_SERVER_HOST=localhost
SQL_SERVER_PORT=1433
SQL_DATABASE=master
SQL_ADMIN_USER=sa
SQL_ADMIN_PASSWORD=<admin-secret>
SQL_AGENT_USER=USR_FDE_RO
SQL_AGENT_PASSWORD=<agent-secret>
SQL_CONNECT_TIMEOUT_SECONDS=10
Agent_llm=OLLAMA
```

Validate configuration before connecting:
```
python scripts\check_startup.py
python scripts\check_startup.py --check-sql
```

- python scripts\ingest_legacy_data.py

## Phase 1: Twin schema and deterministic fleet

After the legacy view/security setup is complete, apply the Phase 1 migration
with the same SQL administrator connection:
```
sqlcmd -S localhost,1433 -d master -U sa -P "<admin-secret>" ^
  -i scripts\migrations\001_create_twin_schema.sql
```

Seed five reproducible Mumbai–Pune refrigerated vehicles, shipments, routes,
and warehouses:
```
python scripts\seed_twin.py
```

The simulator can be exercised without SQL:
```
python -c "from src.twin.telemetry_simulator import build_demo_fleet, TelemetrySimulator; s=TelemetrySimulator(build_demo_fleet(), seed=42); print(s.tick())"
```

The original `dbo.TBL_SC_FLEET_HIST_RAW` data is not modified. Phase 1
telemetry is stored in the `Twin` schema and is labelled `simulator`.

## Phase 2: predictive intelligence and audit metadata

Apply the Phase 2 audit migration after the Phase 1 schema:
```
sqlcmd -S localhost,1433 -d master -U sa -P "<admin-secret>" ^
  -i scripts\migrations\002_extend_phase2_audit.sql
```

The deterministic risk engine reports `normal`, `warning`, `critical`, or
`unknown`. It estimates temperature-threshold crossing time only; it does not
claim spoilage or remaining shelf life. External weather failures are reported
as `degraded`, and operational actions require an explicit approval state.

## Connecting to the data 

We need to query the database
- Download : https://github.com/microsoft/azuredatastudio
   - https://learn.microsoft.com/en-us/previous-versions/azure-data-studio/download-azure-data-studio?tabs=win-install%2Cwin-user-install%2Credhat-install%2Cwindows-uninstall%2Credhat-uninstall
- The recommendation is to use VS code extension : "SQL Server (mssql)" by microsoft
   - Click on icon that looks like server or refrigarator, not the one with cylinder 
   - Add connection
   - Fill the below :
   ```
   Profile Name: legacy-mssql
   Server name*: localhost
   Port: 1433
   Trust server certificate: 🟩 Check this box / turn it ON (Crucial for Docker)
   Authentication type*: SQL Login
   User name*: sa
   Password*: Use the secret supplied when the container was created
   Save Password: 🟩 Check this box
   Database name: Type master (or leave it on "Select a database")
   Encrypt: ⚠️ Change this from Mandatory to Optional (or False)
   ```

- CTRL + N
- SQL
- SELECT COUNT(*) AS total_rows FROM dbo.TBL_SC_FLEET_HIST_RAW;

## instruction for Ec2 instance > datbase
- Instance type : c7i-flex.large
- storage : 30 gb
- ubuntu (linux)
- Security group > attach the security while creating ec2 instance
- Launch instance
- SSH using .pem file from your system
- install the docker
- 
```
docker run -v mssql_data:/var/opt/mssql \
  -e "ACCEPT_EULA=Y" \
  -e "MSSQL_SA_PASSWORD=<strong-secret>" \
  -p 1433:1433 \
  --name legacy-mssql \
  -d mcr.microsoft.com/mssql/server:2022-latest
```
- copy the ip address of the ec2 (public)

# Phase 1

## SOP Ingestion

- https://app.pinecone.io/ > get api key
- Use it in .env
- run python scripts\ingest_sop_pinecone.py

# Phase 2

## Data Security

- Click on file : scripts\setup_security_and_view.sql. Run it with the
  `FDE_AGENT_PASSWORD` SQLCMD variable set to the same value as
  `SQL_AGENT_PASSWORD`; the password is never stored in the SQL file.
- VS-code will show you Start button directly on top else run like we were running the commands previously.
- Once done, create a new connection now with Agent-Profile
```
* Profile Name: agent-fde-ro
* Connection Group: Leave it on <Default>
* Input type: Select Parameters (Do not click "Load from Connection String", "Browse Azure", or "Browse Fabric")
* Server name*: localhost
* Port: 1433
* Trust server certificate: 🟩 Check this box / Turn it ON
* Authentication type*: SQL Login
* User name*: USR_FDE_RO
* Password*: Read `SQL_AGENT_PASSWORD` from the environment; never commit it
* Save Password: 🟩 Check this box / Turn it ON
* Database name: Type master (or click "Select a database" and select master)
* Encrypt: Change this from Mandatory to Optional (or False)
```

Connect and test below commands :
```
-- TEST 1: This SHOULD work perfectly (Access to clean view)
SELECT TOP 5 * FROM FDE_VIEWS.VW_ACTIVE_FLEET;

-- TEST 2: This SHOULD fail instantly (Access to raw legacy table is DENIED)
SELECT TOP 5 * FROM dbo.TBL_SC_FLEET_HIST_RAW;
```

## Phase 3: REEFERTWIN command centre

Install the pinned dependencies, including PyDeck, and start the Streamlit
application:
```
pip install -r requirements.txt
streamlit run src\ui.py
```

The command centre provides Overview, Digital Twin, Fleet, Simulation Lab, AI
Command Centre, and Audit pages. The demo projection is held in Streamlit
session state: refreshes and page changes are read-only, while the Simulation
Lab advances state only after an explicit 1-, 5-, or 15-minute action. Reset
uses the fixed seed and reproduces the same baseline observations. PyDeck
renders the Mumbai–Pune route and risk-coloured vehicle markers; if PyDeck is
unavailable, the UI falls back to a map and coordinate table.

The AI Command Centre retains the existing LangGraph chat flow. Configure the
SQL and LLM secrets before using it; the local twin pages do not require live
SQL connectivity.

## Phase 4: what-if simulation and optimization

Use the **What-if Lab** page to create an isolated scenario for
`REEFER-003`. Supported disruptions are compressor failure, heatwave,
temperature spike, traffic congestion, highway closure, capacity reduction,
and warehouse unavailability. Each scenario receives a mandatory scenario ID
and copies baseline telemetry/projections; creating or refreshing a scenario
does not modify the baseline.

The page compares baseline and disrupted temperature/risk, evaluates every
warehouse, and displays rejection reasons for capacity, temperature range,
availability, route, or deadline failures. Route estimates use the
deterministic offline fixture unless a live OSRM adapter is configured.

A diversion follows the explicit lifecycle:
`proposed -> approved -> executed`. Execution is blocked until approval and
changes only the selected scenario projection. If no facility is feasible,
the UI reports an explicit human-logistics escalation instead of inventing a
destination.

## Phase 5: deployment and operations

Run the local readiness check:
```
python scripts\health_check.py
python scripts\health_check.py --check-sql
```

Build and run the pinned container:
```
docker compose up --build
```

The container listens on port `8501`, excludes `.env` from the image, and
reports a health status through the Docker health check. The GitHub Actions
workflow runs compile, unit-test, offline-health, and container-build gates on
`main`. Deployment remains manual and runs the same startup/test gates on the
EC2 host before restarting Streamlit and checking `/_stcore/health`.

Apply SQL migrations separately with an administrator/migration identity.
Runtime secrets belong in GitHub/EC2 secret storage or the host environment;
do not place them in the image, repository, or workflow command output.

Step-1 : Pass below in the dispatcher >
- Question-1 (The "Domino Effect" Test)
```
Find any active shipments near Los Angeles (Latitude ~33.8, Longitude ~-118.1). Check the local weather there, and tell me if the current cargo temperature violates the SOP for fresh perishables.
```

- Question-2 (The "Restraint" Test (No-Tool Routing))
```
I'm a new dispatcher on the night shift. Can you quickly explain the difference between a Tier 1 and Tier 2 escalation?
```


## Phase 4
Go to VS-code > CTRL + N > 'click on plain-text' and use 'sql'

Select the su user and write below :

CREATE TABLE FDE_VIEWS.AgentAuditLog (
    LogID INT IDENTITY(1,1) PRIMARY KEY,
    Timestamp DATETIME DEFAULT GETDATE(),
    SessionID VARCHAR(50),
    NodeExecuted VARCHAR(50),
    ToolName VARCHAR(100),
    Content NVARCHAR(MAX) -- NVARCHAR to safely handle JSON strings and large LLM outputs
);

-- Grant the agent user permission to write only to this specific table
```
GRANT INSERT ON FDE_VIEWS.AgentAuditLog TO USR_FDE_RO;
```

## Phase 5
streamlit run src\ui.py

## Phase 6
- Deployment
```
sudo apt update && sudo apt install -y python3-pip python3-venv git
cd /home/ubuntu
git clone https://github.com/nimowhyca/cold-chain-logistics-FDE-Project.git
cd cold-chain-logistics-FDE-Project
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run src/ui.py
```

1. Add the Microsoft GPG repository key
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg

2. Add the Microsoft SQL Server Ubuntu repository
curl -fsSL https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list

3. Update apt and install the driver (Accepting the EULA)
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18

4. Install the unixODBC development headers
sudo apt-get install -y unixodbc-dev

5. Create the systemd service file
```
sudo nano /etc/systemd/system/streamlit.service
```

6. Paste the configuration
```
[Unit]
Description=Streamlit Cold-Chain Dispatch Console
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/cold-chain-logistics-FDE-Project
ExecStart=/home/ubuntu/cold-chain-logistics-FDE-Project/venv/bin/streamlit run src/ui.py --server.port=8501 --server.address=0.0.0.0
Restart=always

[Install]
WantedBy=multi-user.target
```

7. Register and start the service
```
sudo systemctl daemon-reload
sudo systemctl enable streamlit
sudo systemctl start streamlit
```